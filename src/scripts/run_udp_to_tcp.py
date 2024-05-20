#!/usr/bin/env python3

import argparse
from subprocess import Popen
from os import path


channel_configs = {
    #channel_name: (UDP port, TCP port, decoder args),
    'abc': (50001, 60001, '0x31 0x34 720p60 120 900 10248'),   # KGO
    'nbc': (50002, 60002, '0x31 0x34 1080i30 60 900 10248'),   # KNTV
    'fox': (50003, 60003, '0x31 0x34 720p60 120 900 10248'),   # KTVU
    'kron': (50004, 60004, '0x71 0x74 720p60 120 900 10248'),  # KRON
    'kpyx': (50005, 60005, '0x31 0x34 1080i30 60 900 10248'),  # KPYX (KPIX+)
    'cbs': (50006, 60006, '0x31 0x34 1080i30 60 900 10248'),   # KPIX
    'pbs': (50007, 60007, '0x31 0x34 1080i30 60 900 10248'),   # KQED
    'univision': (50008, 60008, '0x31 0x34 720p60 120 900 10248'),  # KDTV
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('channel', nargs='+')
    args = parser.parse_args()

    src_dir = path.dirname(path.dirname(path.abspath(__file__)))
    udp_to_tcp_path = path.join(src_dir, 'forwarder', 'udp_to_tcp')

    procs = []

    for channel in args.channel:
        config = channel_configs[channel]
        cmd = [udp_to_tcp_path, str(config[0]), str(config[1])]
        print(' '.join(cmd))
        procs.append(Popen(cmd))

    for proc in procs:
        proc.communicate()


if __name__ == '__main__':
    main()
