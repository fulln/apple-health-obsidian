# Health Auto Export JSON Notes

The observed JSON shape is:

```json
{
  "data": {
    "metrics": [
      {"name": "step_count", "units": "count", "data": [{"qty": 123, "date": "..."}]}
    ]
  }
}
```

Metric records usually contain `qty`, `date`, and `source`. Some aggregate metrics use `Avg`, `Min`, and `Max`.

Important daily metrics:

- Activity: `step_count`, `apple_exercise_time`, `apple_stand_hour`, `apple_stand_time`, `active_energy`, `basal_energy_burned`, `physical_effort`
- Movement: `walking_running_distance`, `walking_speed`, `walking_step_length`, `walking_double_support_percentage`, `walking_asymmetry_percentage`, `stair_speed_down`, `six_minute_walking_test_distance`
- Heart and recovery: `heart_rate`, `resting_heart_rate`, `walking_heart_rate_average`, `heart_rate_variability`, `blood_oxygen_saturation`, `respiratory_rate`
- Sleep: `sleep_analysis`
- Body: `weight_body_mass`, `body_mass_index`, `body_fat_percentage`, `lean_body_mass`
- Environment and habits: `time_in_daylight`, `headphone_audio_exposure`, `handwashing`

Unit handling:

- `active_energy` and `basal_energy_burned` may be exported as `kJ`; report kcal as `kJ / 4.184`.
- `sleep_analysis` values are exported in hours.
- `walking_running_distance` is exported in kilometers in the observed files.

The report should not pass full raw health samples to AI unless needed. Prefer deterministic aggregation first, then send compact facts to the model.
