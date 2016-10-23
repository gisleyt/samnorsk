#!/usr/bin/env bash

programname=$0

function usage {
    echo "usage: $programname [-r] [-n infile] [-b infile] [-o outfile]"
    echo "	-n inputnynorsk    nynorsk json file"
    echo "	-b inputbokmaal    bokmaal json file"
    echo "	-o output  dictionary output file"
    echo "	-r reduction      use synonym by reduction (default is expansion)"
    exit 1
}

REDUCTION=NO
while [[ $# -gt 1 ]]
do
key="$1"

case $key in
    -n|--inputnynorsk)
    NYNORSK="$2"
    shift # past argument
    ;;
    -b|--inputbokmaal)
    BOKMAAL="$2"
    shift # past argument
    ;;
    -o|--output)
    OUTPUT="$2"
    shift # past argument
    ;;
    -r|--reduction)
    REDUCTION=YES
    ;;
    *)
            # unknown option
    ;;
esac
shift # past argument or value
done

if [[ -z "$NYNORSK" || -z "$BOKMAAL" || -z "$OUTPUT" ]]
then
    usage
    exit -1
fi

jq  .text $NYNORSK | sed 's/\\n/ /g' > /tmp/nynorsk.json.jqed &
jq  .text $BOKMAAL | sed 's/\\n/ /g' > /tmp/bokmaal.json.jqed
apertium -f txt nob-nno /tmp/bokmaal.json.jqed /tmp/bokmaal.json.jqed.nynorsk &
apertium -f txt nno-nob /tmp/nynorsk.json.jqed /tmp/nynorsk.json.jqed.bokmaal
python /software/bin/create_synonyms.py /tmp/nynorsk.json.jqed /tmp/nynorsk.json.jqed.bokmaal /tmp/bokmaal.json.jqed.nynorsk /tmp/bokmaal.json.jqed $OUTPUT
