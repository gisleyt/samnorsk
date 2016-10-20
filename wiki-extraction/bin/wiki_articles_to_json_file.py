#!/usr/bin/env python

# noinspection PyUnresolvedReferences
from builtins import str

import io
import json
import logging
import os
import sys
from argparse import ArgumentParser

sys.path.append(os.path.join(os.path.abspath(os.path.dirname(__file__)), '..', 'lib'))

from wikipedia import article_gen


def main():
    parser = ArgumentParser()

    parser.add_argument('-d', '--dump-file')
    parser.add_argument('-o', '--out-file')
    parser.add_argument('-l', '--limit', default=None, type=int)
    parser.add_argument('-p', '--procs', default=1, type=int)

    opts = parser.parse_args()

    dump_fn = opts.dump_file
    out_fn = opts.out_file
    limit = opts.limit
    parser_procs = opts.procs

    if not dump_fn or not out_fn:
        sys.exit(1)

    count = 0

    with io.open(out_fn, mode='w', encoding='utf-8') as f:
        for obj in article_gen(dump_fn, num_articles=limit, n_procs=parser_procs):
            count += 1

            if count % 10000 == 0:
                logging.info('Read %d articles ...' % count)

            out_obj = {'id': obj['id'], 'title': obj['title'], 'text': obj['article.text']}

            f.write(json.dumps(out_obj, ensure_ascii=False))
            f.write(u'\n')


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    main()