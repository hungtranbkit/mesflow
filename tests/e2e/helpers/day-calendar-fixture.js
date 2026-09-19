// Existing UI layout/quantity fixtures intentionally use a 24h work calendar.
// Real lunch behavior is covered by dashboard-employee-timeline and API tests.
module.exports.fullDayContext={target_minutes:1440,intervals:[
  {interval_type:'WORK',start_minute:0,end_minute:1440,sort_order:0}
]};
