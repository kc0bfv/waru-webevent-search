#!/usr/bin/env bash
set -euo pipefail

IND=0
OUTDIR="../../public"

ls */*.html \
  | xargs -I {} echo '\"{}\"' \
  | xargs -L 99 echo \
  | while IFS= read -r FILES_TO_ZIP; do
  OUT_NAME=$(printf "spo_%03i.zip" $IND)
  bash -c "zip -ur $OUTDIR/$OUT_NAME $FILES_TO_ZIP"

  IND=$(($IND + 1))
done

IND=$(($IND - 1))

echo $IND > LASTINDEX
zip -ur "$OUTDIR/spo_index.zip" LASTINDEX
rm LASTINDEX
