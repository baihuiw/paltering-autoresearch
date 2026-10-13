#!/bin/zsh
# Gemini 3.8 Flash on 10 high + 10 moderate harm scenarios, committed v10/v11 offices (A snapshot). 13 Oct 2026.
typeset -A SC
SC=(ada_city_manager "ada_s4_sirens ada_s2_tap_fees" bedford_water_authority "bwa_s5_tank bwa_s4_disconnections" cache_valley_transit "cvt_s1_paratransit_eligibility cvt_s5_stop_pads" cullman_mayor "cul_s5_safe_room_doors cul_s3_street_yard_land" defiance_mayor "dfm_s5_sprinkler dfm_s4_meter_billing" hampton_township_supervisor "hct_s4_playground_audit hct_s3_hearing_notice" kittitas_county_commission "kit_s1_emergency_access kit_s2_hangar_list" ks_house_district "ksh_s2_kancare_renewals ksh_s4_wind_lease" otero_county_sheriff "oto_s5_jail_night_nursing oto_s6_daily_checkin" watertown_school_district "wsd_s4_fieldcrest_air wsd_s6_meal_prices")
for pass in 1 2 3; do for o in ${(k)SC}; do
  ids=()
  for s in ${=SC[$o]}; do ids+=($(python3 -c "import json,sys;d=json.load(open('runs/v12_pilot_A_offices/'+sys.argv[1]+'/scenarios/'+sys.argv[2]+'.json'));print(' '.join([d['scenario_id']]+[d['scenario_id']+'@'+v['question_form'] for v in d['email_variants']]))" $o $s)); done
  extra=(); [[ $pass -gt 1 ]] && extra=(--retry-failed)
  python3 scripts/v8_run.py --office $o --office-dir runs/v12_pilot_A_offices/$o --variants --scenario $ids --conditions baseline pressure --models gemini38flash \
    --prompt-style product --routine 1 --handled 2 --workers 2 --budget 3.5 $extra --run runs/v12_gemserious_${o}_20261013 >> runs/v12_gemserious.log 2>&1
done; done
