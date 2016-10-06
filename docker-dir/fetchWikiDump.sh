#!/bin/bash -

wget https://dumps.wikimedia.org/nnwiki/latest/nnwiki-latest-pages-articles.xml.bz2 &
wget https://dumps.wikimedia.org/nowiki/latest/nowiki-latest-pages-articles.xml.bz2
bunzip2 nnwiki-latest-pages-articles.xml.bz2
bunzip2 nowiki-latest-pages-articles.xml.bz2
