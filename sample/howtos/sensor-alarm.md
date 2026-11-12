# Answer a sensor alarm

Made up, like the rest of Fernhollow.

When a Tidepool sensor sends no readings for an hour, the **Sensor readings** routine says so.

1. Look at the routine's last lines: which sensor went quiet, and since when.
2. Check the sensor's battery report in `readings/battery.csv`.
3. If the battery is under 20%, add a task for a visit to the field.
4. If the battery is fine, run `make check-radio` and note what it prints.

Never change the firmware to quiet an alarm.
