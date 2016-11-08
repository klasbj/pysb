#echo "\$1 ^!2 !3 4 5 \$6|[]=|ksjdnf" | python pysb.

gen_input() {
  cat test/input.1
  while true; do
    cat test/input.seq.1
    sleep 3
    cat test/input.seq.2
    sleep 3
  done
}

gen_input | python pysb.py
