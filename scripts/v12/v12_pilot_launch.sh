#!/bin/zsh
# usage: v12_pilot_launch.sh A|B   (A = control snapshot, B = edited data/v8/offices)
V=$1
PAR=${2:-}
typeset -A SC
SC=(cache_valley_transit "cvt_s4_sunday_pilot" otero_county_sheriff "oto_s1_k9_program" watertown_school_district "wsd_s5_fall_screener wsd_s1_activity_route" kittitas_county_commission "kit_s5_fair_premiums" cullman_mayor "cul_s1_cemetery_spaces" ada_city_manager "ada_s3_landfill_rate" hampton_township_supervisor "hct_s2_curbside_recycling" ks_house_district "ksh_s5_childcare_center" bedford_water_authority "bwa_s2_odor_control")
for o in ${(k)SC}; do
  ids=()
  for s in ${=SC[$o]}; do ids+=($(python3 -c "import json,glob,sys;d=json.load(open(glob.glob('data/v8/offices/*/scenarios/'+sys.argv[1]+'.json')[0]));print(' '.join([d['scenario_id']]+[d['scenario_id']+'@'+v['question_form'] for v in d['email_variants']]))" $s)); done
  if [[ $V == A ]]; then od=(--office-dir runs/v12_pilot_A_offices/$o); else od=(); fi
  python3 scripts/v8_run.py --office $o $od --variants --scenario $ids --conditions baseline pressure --models grok47 gemini38flash \
    --prompt-style product --routine 1 --handled 2 --workers 6 --budget 12 $PAR --run runs/v12_pilot_${V}_${o}_20261013 > runs/v12_pilot_${V}_${o}_20261013.log 2>&1 &
done
wait
