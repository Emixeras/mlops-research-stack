from typing import Union

import dagster as dg

_all_assets_job = dg.define_asset_job("all_assets")

@dg.schedule(cron_schedule="@daily", job=_all_assets_job)
def daily_all(context: dg.ScheduleEvaluationContext) -> Union[dg.RunRequest, dg.SkipReason]:
    return dg.SkipReason("Skipping. Change this to return a RunRequest to launch a run.")
