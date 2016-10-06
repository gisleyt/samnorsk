# samnorsk
Docker image which creates elastic synonym dictionaries for bokmål/nynorsk using apertium.

The docker image can be built with:

~~~~
docker build -t  <image-name> docker-dir/.
~~~~

Test the image with:

~~~~
mkdir -p /tmp/samnorsk
docker run -v /tmp/samnorsk:/mnt/samnorsk <image-name> python helloapertium.py /mnt/samnorsk
~~~~

helloapertium.py will translate a simple sentence, and add the translation to /tmp/samnorsk.