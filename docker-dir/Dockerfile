FROM ubuntu:16.04
MAINTAINER Gisle Ytrestol <gisleyt@gmail.com>

RUN apt-get update && apt-get install -y \
    wget \
    curl \
    sudo \
  && wget http://apertium.projectjj.com/apt/install-nightly.sh -O - | sudo bash \
  && apt-get update \
  && apt-get -f install -y apertium-all-dev apertium-nno apertium-nob apertium-nno-nob bzip2 python-pip python-dev build-essential \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

RUN locale-gen en_US.UTF-8
ENV LANG en_US.UTF-8
ENV LANGUAGE en_US:en
ENV LC_ALL en_US.UTF-8

RUN mkdir -p /samnorsk
ADD helloapertium.py /samnorsk
ADD createDictionary.py /samnorsk
ADD fetchWikiDump.sh /samnorsk
WORKDIR /samnorsk

## These wgets will not be part for the final image as we will then download them on demand, but it's nice to have during development.
RUN wget https://dumps.wikimedia.org/nnwiki/latest/nnwiki-latest-pages-articles.xml.bz2 -O /samnorsk/nnwiki-latest-pages-articles.xml.bz2 && bunzip2 /samnorsk/nnwiki-latest-pages-articles.xml.bz2
RUN wget https://dumps.wikimedia.org/nowiki/latest/nowiki-latest-pages-articles.xml.bz2 -O /samnorsk/nowiki-latest-pages-articles.xml.bz2 && bunzip2 /samnorsk/nowiki-latest-pages-articles.xml.bz2


