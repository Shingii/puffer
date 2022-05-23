#!/usr/bin/env python3

import os
import sys
import yaml
import math
import time
import argparse
import signal
from os import path
from datetime import datetime, timedelta
from helpers import Popen, check_call


CL_HOUR = 4  # perform continual learning at 4:00 (UTC)


def run_ttp(ttp_path, yaml_settings_path):
    # load YAML settings from the disk
    with open(yaml_settings_path, 'r') as fh:
        yaml_settings = yaml.safe_load(fh)

    new_model_dir = None

    # only retrain one model for now: bbr, puffer_ttp_cl ("bbr-DATE-i")
    for expt in yaml_settings['experiments']:
        fingerprint = expt['fingerprint']

        if ('abr_name' not in fingerprint or
            fingerprint['abr_name'] != 'puffer_ttp_cl'):
            continue

        cc = fingerprint['cc']
        if cc != 'bbr':
            continue

        # find a name for the new model_dir
        old_model_dir = fingerprint['abr_config']['model_dir']
        model_parent_dir = path.dirname(old_model_dir)

        new_model_base_prefix = cc + '-' + datetime.utcnow().strftime('%Y%m%d')
        # increment i until a non-existent directory is found
        i = 0
        while True:
            i += 1
            new_model_base = new_model_base_prefix + '-' + str(i)
            new_model_dir = path.join(model_parent_dir, new_model_base)
            if not path.isdir(new_model_dir):
                break

        # run ttp.py
        start_time = time.time()
        sys.stderr.write('Continual learning: loaded {} and training {}\n'
                         .format(path.basename(old_model_dir), new_model_base))

        check_call([ttp_path, yaml_settings_path, '--cl', '--cc', cc,
                    '--load-model', old_model_dir,
                    '--save-model', new_model_dir])

        end_time = time.time()
        sys.stderr.write(
            'Continual learning: new model {} is available after {:.2f} hours\n'
            .format(new_model_base, (end_time - start_time) / 3600))

        # back up new model
        tar_file = '{}.tar.gz'.format(new_model_base)
        check_call('tar czvf {} {}'.format(tar_file, new_model_base),
                   shell=True, cwd=model_parent_dir)
        gs_url = 'gs://puffer-models/puffer-ttp/{}'.format(tar_file)
        check_call('gsutil cp {} {}'.format(tar_file, gs_url),
                   shell=True, cwd=model_parent_dir)

    if new_model_dir is None:
        sys.stderr.write('Warning: not performing continual learning\n')
        return

    # update model_dir
    for expt in yaml_settings['experiments']:
        fingerprint = expt['fingerprint']

        # share the new model among all abr_name containing 'puffer_ttp_cl'
        if ('abr_name' not in fingerprint or
            'puffer_ttp_cl' not in fingerprint['abr_name']):
            continue

        cc = fingerprint['cc']
        if cc != 'bbr':
            continue

        fingerprint['abr_config']['model_dir'] = new_model_dir

    # write YAML settings with updated model_dir back to disk
    with open(yaml_settings_path, 'w') as fh:
        yaml.safe_dump(yaml_settings, fh, default_flow_style=False)
    sys.stderr.write('Updated model_dir in {}\n'.format(yaml_settings_path))


def main():
    parser = argparse.ArgumentParser(
        description='start "run_servers" and continual learning at '
                    '{}:00 (UTC)'.format(CL_HOUR))
    parser.add_argument('yaml_settings')
    parser.add_argument('--save-log', action='store_true')
    args = parser.parse_args()

    yaml_settings_path = path.abspath(args.yaml_settings)
    src_dir = path.dirname(path.dirname(path.abspath(__file__)))
    run_servers_path = path.join(src_dir, 'media-server', 'run_servers')
    cleaner_path = path.join(src_dir, 'cleaner', 'cleaner')
    ttp_path = path.join(src_dir, 'scripts', 'ttp.py')

    try:
        curr_dt = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')

        if args.save_log:
            logfile = open('run_servers_{}.log'.format(curr_dt), 'w')
        else:
            logfile = open(os.devnull, 'w')

        # execute run_servers
        run_servers_proc = Popen([run_servers_path, yaml_settings_path],
                                 preexec_fn=os.setsid, stderr=logfile)
        sys.stderr.write('Started run_servers\n')

        while True:
            # sleep until next CL_HOUR
            td = datetime.utcnow()
            wakeup = datetime(td.year, td.month, td.day, CL_HOUR, 0)
            if wakeup <= td:
                wakeup += timedelta(days=1)

            sys.stderr.write('Sleeping until {} (UTC) to perform '
                             'continual learning\n'.format(wakeup))
            time.sleep(math.ceil((wakeup - td).total_seconds()))

            # perform continual learning!
            run_ttp(ttp_path, yaml_settings_path)

            # kill and restart run_servers with updated YAML settings
            if run_servers_proc:
                os.killpg(os.getpgid(run_servers_proc.pid), signal.SIGTERM)

            # restart Gunicorn
            check_call('sudo systemctl restart gunicorn', shell=True)

            # clean old video files
            check_call('{} -r -p "\d+\.(m4s|chk|ssim)" '
                       '-t 600 /dev/shm/media'.format(cleaner_path), shell=True)

            run_servers_proc = Popen([run_servers_path, yaml_settings_path],
                                     preexec_fn=os.setsid, stderr=logfile)
            sys.stderr.write('Killed and restarted run_servers with updated '
                             'YAML settings\n')
    except Exception as e:
        print(e, file=sys.stderr)
    finally:
        # clean up in case on exceptions
        if run_servers_proc:
            os.killpg(os.getpgid(run_servers_proc.pid), signal.SIGTERM)
        logfile.close()


if __name__ == '__main__':
    main()
