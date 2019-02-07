#!/usr/bin/env python3

import argparse
import csv
import sys
from collections import defaultdict, Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from signal import signal, SIGINT

from sklearn.feature_extraction import DictVectorizer
from sklearn.metrics.pairwise import cosine_similarity as sim

signal(SIGINT, lambda signum, frame: sys.exit(1))

parser = argparse.ArgumentParser()
parser.add_argument('wsi', type=argparse.FileType('r'))
args = parser.parse_args()

wsi = defaultdict(dict)
D = []

with args.wsi as f:
    reader = csv.reader(f, delimiter='\t', quoting=csv.QUOTE_NONE)
    for row in reader:
        word, sid, _, words = row

        try:
            words = {k: float(v) for record in words.split('  ') for k, v in (record.rsplit(':', 1),)}
        except ValueError:
            print('Skipping misformatted string: %s.' % words, file=sys.stderr)
            continue

        wsi[word][int(sid)] = words
        D.append(words)

v = DictVectorizer().fit(D)


def emit(word):
    senses = {}

    for sid, words in wsi[word].items():
        sense = '%s#%d' % (word, sid)

        senses[sense] = {}

        vector = v.transform({**words, **{word: 1.}})

        for neighbour, weight in words.items():
            candidates = Counter(
                {nsid: sim(v.transform(neighbours), vector).item(0) for nsid, neighbours in wsi[neighbour].items()})

            if not candidates:
                print('Missing candidates for "%s": "%s".' % (word, neighbour), file=sys.stderr)
                continue

            for nsid, cosine in candidates.most_common(1):
                if cosine > 0:
                    nsense = '%s#%d' % (neighbour, nsid)
                    senses[sense][nsense] = weight
                else:
                    print('Cannot estimate the sense for "%s": "%s".' % (word, neighbour), file=sys.stderr)

    return senses


with ProcessPoolExecutor() as executor:
    futures = (executor.submit(emit, word) for word in wsi)

    for i, future in enumerate(as_completed(futures)):
        senses = future.result()

        for sense, nsenses in senses.items():
            for nsense, weight in nsenses.items():
                print('%s\t%s\t%f' % (sense, nsense, weight))

        if (i + 1) % 1000 == 0:
            print('%d entries out of %d done.' % (i + 1, len(wsi)), file=sys.stderr)

if len(wsi) % 1000 != 0:
    print('%d entries out of %d done.' % (len(wsi), len(wsi)), file=sys.stderr)
