#!/bin/bash

table="$1"
column="$2"
binSize="$3"

export PGPASSWORD=password

psql -h 127.0.0.1 -U cosmicweb -d cosmic -F $'\t' --no-align -c "select floor(\"${column}\" / ${binSize})*${binSize} as \"bins\", count(*) as count from ${table} group by \"bins\" order by \"bins\"" > plot_db_histogram.plotdata

gnuplot plot_db_histogram.plotfile
