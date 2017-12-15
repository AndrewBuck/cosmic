#!/bin/bash

if [ $# -ne 1 ]
then
    echo -en "\n\n\tUSAGE: ./import_all.sh <path_to_catalog_directory>/\n\n"
    exit
fi

catalogPath="${1%/}"

time python3 createQuestions.py

time python3 import_cat_messier.py

time python3 import_cat_exoplanets.py ${catalogPath}/exoplanets/exoplanets.csv

time python3 import_cat_gcvs.py ${catalogPath}/gcvs/gcvs5.txt

time python3 import_cat_astorb.py ${catalogPath}/astorb/astorb.dat

time python3 calculate_astorb_ephemerides.py 2017 2018 29 5

time python3 import_cat_2mass_xsc.py ${catalogPath}/2mass/xsc_aaa ${catalogPath}/2mass/xsc_baa

time python3 import_cat_geoip_geolitecity.py ${catalogPath}/ip/GeoLiteCity_20170905/GeoLiteCity-Location.csv ${catalogPath}/ip/GeoLiteCity_20170905/GeoLiteCity-Blocks.csv

time python3 import_cat_ucac4_dump.py ${catalogPath}/ucac4/ascii_dump/z*.asc

