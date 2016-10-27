import logging
import os
import sys
from argparse import ArgumentParser
from itertools import islice

from elasticsearch import helpers
from elasticsearch.client import Elasticsearch
from elasticsearch.client.indices import IndicesClient

sys.path.append(os.path.join(os.path.abspath(os.path.dirname(__file__)), '..', 'lib'))

from wikipedia import articles


def main():
    parser = ArgumentParser()
    parser.add_argument('-d', '--dump-file')
    parser.add_argument('-e', '--elasticsearch-host', default='localhost:9200')
    parser.add_argument('-i', '--index', default='wikipedia')
    parser.add_argument('-l', '--limit', default=0, type=int)
    parser.add_argument('-p', '--id-prefix')
    opts = parser.parse_args()

    dump_fn = opts.dump_file
    es_host = opts.elasticsearch_host
    es_index = opts.index
    limit = opts.limit if opts.limit > 0 else None
    prefix = opts.id_prefix

    if not dump_fn:
        logging.error('missing filenames ...')
        sys.exit(1)

    gen = articles(dump_fn, limit=limit)

    es = Elasticsearch(hosts=[es_host])
    ic = IndicesClient(es)

    if not ic.exists(es_index):
        ic.create(es_index)

    while True:
        chunk = islice(gen, 0, 1000)

        actions = [{'_index': es_index,
                    '_type': 'article',
                    '_id': article['id'] if not prefix else '%s-%s' % (prefix, article['id']),
                    '_source': article}
                   for article in chunk]

        if not actions:
            break

        helpers.bulk(es, actions)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    main()