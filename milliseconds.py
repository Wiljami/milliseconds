#!/usr/bin/python3
"""Nginx access log analyzer"""

import json
import sys
import re

from pprint import pprint


def add_counters(data, category):

    # Set baseline if first value
    if result[category]['count'] == 0:
        result[category]['max'] = data['duration']
        result[category]['min'] = data['duration']

    if data['duration'] > result[category]['max']:
        result[category]['max'] = data['duration']

    if data['duration'] < result[category]['min']:
        result[category]['min'] = data['duration']

    # Increment counters
    result[category]['count'] += 1
    result[category]['sum'] += data['duration']
    result[category]['avg'] = \
        int(result[category]['sum'] / result[category]['count'])

    result[category]['bytes'] += data['bytes']

    return result


def get_top_10(result_type, result_type_dict):
    result = dict()
    for entry in sorted(
            result_type_dict,
            key=result_type_dict.__getitem__,
            reverse=True)[0:9]:

        result[entry] = result_types[result_type][entry]

    return result


bucket = {
    'count': 0,
    'min': 0,
    'max': 0,
    'avg': 0,
    'sum': 0,
    'bytes': 0,
    #  '95th_percentile': 0
}
result = {
    'total': dict(bucket),
    'cache_none': dict(bucket),
    'cache_hit': dict(bucket),
    'cache_miss': dict(bucket),
    'cache_other': dict(bucket),
    '2xx': dict(bucket),
    '3xx': dict(bucket),
    '4xx': dict(bucket),
    '5xx': dict(bucket),
    # sites in maintenance mode should not be counted in the 5xx error bucket
    '503': dict(bucket),
    'internal': dict(bucket)
}

result_types = {
    'hostname': dict(),
    'remote_addr': dict(),
    'remote_user': dict(),
    'request_type': dict(),
    'protocol': dict(),
    'status': dict(),
    'cache': dict(),
}

lineformat = (
    r'(?P<hostname>[^ ]+) '
    r'(?P<remote_addr>[^ ]+) '
    r'- '
    r'(?P<remote_user>[^\[]+) '
    r'\[(?P<time>.+)\] '
    # Clients can name their methods whatever, e.g. CCM_POST
    r'"(?P<request_type>[A-Z_]+) '
    r'(?P<request_url>[^"]+) '
    r'(?P<protocol>[^ ]+)" '
    r'(?P<status>[0-9]+) '
    r'(?P<bytes>[0-9]+) '
    r'"(?P<referer>[^"]*)" '
    r'"(?P<user_agent>[^"]*)" '
    r'(?P<cache>[A-Z-]+) '
    r'"(?P<server>[^"]+)" '
    r'(?P<duration>[0-9\\.]+)\n')

pattern = re.compile(lineformat)  # Compile the regex to fail if it is invalid
linecounter = 0

if __name__ == '__main__':

    # Open input log and interate all lines
    with open(sys.argv[1], 'r') as f:

        for l in f.readlines():
            linecounter += 1

            match = pattern.search(l)

            if not match:
                print('Unexpected log line contents:', file=sys.stderr)
                pprint(l, stream=sys.stderr)
                # On error, just skip this line and continue with the next one
                # Known issue: eg. invalid request might cause empty $request
                # in nginx, thus producting empty "" after timestamp. Current
                # regexp fails with that.
                # FIXME: Should fix the regexp to cope with known common errors
                continue
            else:
                data = match.groupdict()

            if len(data) != 14:
                print('Unexpected log line length: %d' % len(data),
                      file=sys.stderr)
                pprint(l, stream=sys.stderr)
                sys.exit(1)

            # Collect each unique data type
            for type in result_types.keys():
                if data[type] not in result_types[type]:
                    result_types[type][data[type]] = 1
                else:
                    result_types[type][data[type]] += 1

            # Analyze line and update counters
            if data:
                # Convert to milliseconds
                data['duration'] = int(float(data['duration']) * 1000)
                data['bytes'] = int(data['bytes'])
                add_counters(data, 'total')

            if '-' in data['cache'] or 'BYPASS' in data['cache']:
                add_counters(data, 'cache_none')
            elif 'HIT' in data['cache']:
                add_counters(data, 'cache_hit')
            elif 'MISS' in data['cache']:
                add_counters(data, 'cache_miss')
            else:
                add_counters(data, 'cache_other')

            # Track 503 status separately from other 5xx responses
            if data['status'] == '503':
                add_counters(data, '503')
            else:
                add_counters(data, data['status'][0] + 'xx')

            if 'Zabbix' in data['user_agent'] or \
               'Seravo' in data['user_agent'] or \
               'SWD' in data['user_agent']:
                add_counters(data, 'internal')

        # Extend results with top-10 lists for each result type
        for result_type in result_types:
            result['top-' + result_type] = get_top_10(
                result_type, result_types[result_type])

        # Output results
        print(json.dumps(result, indent=4))

        # Debug: print log data types
        debug = False
        if debug:
            print('Total lines analyzed: %d' % linecounter)
            print('Total requests calculated: %d' % result['total']['count'])
