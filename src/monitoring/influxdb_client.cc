#include "influxdb_client.hh"

#include <iostream>
#include "http_request.hh"

using namespace std;
using namespace PollerShortNames;

InfluxDBClient::InfluxDBClient(Poller & poller,
                               const Address & address,
                               const string & database,
                               const string & user,
                               const string & password)
{
  influxdb_addr_ = address;
  sock_.connect(influxdb_addr_);

  database_ = database;
  user_ = user;
  password_ = password;

  poller.add_action(Poller::Action(sock_, Direction::In,
    [this]()->Result {
      /* must read HTTP responses from InfluxDB, then basically ignore them */
      const string response = sock_.read();
      if (response.empty()) {
        throw runtime_error("peer socket in InfluxDB has closed");
      }

      return ResultType::Continue;
    }
  ));

  poller.add_action(Poller::Action(sock_, Direction::Out,
    [this]()->Result {
      while (not buffer_.empty()) {
        string & data = buffer_.front();

        const size_t bytes_written = sock_.nb_write(data);
        if (bytes_written == 0) { // EWOULDBLOCK
          break;
        } else if (bytes_written < data.size()) { // partial write
          data.erase(0, bytes_written);
        } else { // full write
          buffer_.pop_front();
        }
      }

      return ResultType::Continue;
    },
    [this]()->bool {
      return not buffer_.empty();
    }
  ));
}

void InfluxDBClient::post(const string & payload,
                          const std::string & precision)
{
  HTTPRequest request;
  request.set_first_line("POST /write?db=" + database_ + "&u=" + user_ + "&p="
                         + password_ + "&precision=" + precision + " HTTP/1.1");

  request.add_header(HTTPHeader{"Host", influxdb_addr_.str()});
  request.add_header(HTTPHeader{"Content-Type",
                                "application/x-www-form-urlencoded"});
  request.add_header(HTTPHeader{"Content-Length",
                                to_string(payload.size())});
  request.done_with_headers();
  request.read_in_body(payload);
  buffer_.emplace_back(request.str());
}
