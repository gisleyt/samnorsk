# Scripts for extracting wiki data

The docker image is set up with python and the extraction script.

Build the docker image with f.ex. this command:

    docker build -t wiki-extraction .

If you have the wikipedia dump in a folder called data you can set up a docker volume for the input
dump and output json file like f.ex. the following:

    docker run -v `pwd`/data:/data wiki-extraction bash -l -c "wiki_articles_to_json_file.py -d /data/nnwiki-20161001-pages-articles.xml.bz2 -o /data/test.json"

You'll need to run a bash login shell for the environment to be setup.

See bin/wiki_articles_to_json_file.py for command line arguments.

You can then build the frequency MT derived dictionary:

    docker run -v `pwd`/data:/data wiki-extraction bash -l -c "build_dictionary.py -i /data/test.json -o /data/test.txt"