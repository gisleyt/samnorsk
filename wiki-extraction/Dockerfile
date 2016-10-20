FROM ubuntu:16.04
MAINTAINER André Lynum <andre.lynum@nrk.no>

ENV LANG=C.UTF-8 LC_ALL=C.UTF-8

RUN apt-get update -qq -y --fix-missing && apt-get install -y -qq wget bzip2 ca-certificates \
    libglib2.0-0 libxext6 libsm6 libxrender1 \
    git mercurial subversion

RUN echo 'export PATH=/opt/conda/bin:$PATH' > /etc/profile.d/conda.sh && \
    wget --quiet https://repo.continuum.io/miniconda/Miniconda3-latest-Linux-x86_64.sh -O ~/miniconda.sh && \
    /bin/bash ~/miniconda.sh -b -p /opt/conda && \
    rm ~/miniconda.sh

ENV PATH /opt/conda/bin:$PATH

RUN mkdir -p /software
COPY lib /software/lib
COPY bin /software/bin
RUN chmod +x /software/bin/*
RUN echo 'export PATH=/software/bin:$PATH' > /etc/profile.d/software.sh

COPY requirements.txt /software
RUN conda install -q -y --file /software/requirements.txt

# CMD ["/bin/bash", "--login", "-c", "wiki_articles_to_json_file.py"]