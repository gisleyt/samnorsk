#!/usr/bin/env python
# -*- coding: utf-8 -*-

class Article:
    def __init__(self, id, text):
        self.id = id
        self.text = text


class ArticleIterator:
    def __init__(self, wiki_file):
        self.wiki_articles = open(wiki_file, 'r')

    def __iter__(self):
        return self

    def next(self):
        lines = []
        id = ""
        while (True):
            next_line = self.wiki_articles.readline()
            if next_line == "":
                self.wiki_articles.close()
                raise StopIteration()
            elif "<doc id=" in next_line:
                id = next_line[9:next_line[9:].index("\"") + 9]
            elif "</doc>" in next_line:
                break
            else:
                lines.append(next_line.strip())
        return Article(id, " ".join(lines))



def main():
    iter = ArticleIterator("../resources/noall.txt")
    for fo in iter:
        if fo.id.endswith("00"):
            print fo.text



if __name__ == '__main__':
    main()