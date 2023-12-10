function set_jobs() {
  var dept_id = $('#dept').val();
  // fetch jobs for dept_id and modify #job_ids <select>
  var sel_job = $('#job_title').val();
  var sel_job_exists = false;
  var jobs_url = $('#add-assignment-form').data('jobs-url');
  var jobs = $.ajax({
    url: jobs_url,
    data: {department_id: dept_id}
  }).done(function(jobs) {
    $('#job_title').replaceWith('<select id="job_title" name="job_title">');
    for (i = 0; i < jobs.length; i++) {
      $('select#job_title').append(
        $('<option></option>').attr("value", jobs[i][0]).text(jobs[i][1])
      );
      if (jobs[i][0]==sel_job) { sel_job_exists = true }
    }
    if (sel_job_exists == true) { $('#job_title').val(sel_job) } // if possible keep selected job
  });
  var sel_unit = $('#unit').val();
  var sel_unit_exists = false;
  var units_url = $('#add-assignment-form').data('units-url');
  var units = $.ajax({
    url: units_url,
    data: {department_id: dept_id}
  }).done(function(units) {
    $('#unit').replaceWith('<select id="unit" name="unit">');
    for (i = 0; i < units.length; i++) {
      $('select#unit').append(
        $('<option></option>').attr("value", units[i][0]).text(units[i][1])
      );
      if (units[i][0]==sel_unit) { sel_unit_exists = true }
    }
    if (sel_unit_exists == true) { $('#unit').val(sel_unit) } // if possible keep selected unit
  });
}

$(document).ready(function() {
  set_jobs();
  $('select#dept').change(set_jobs);
});

/*
$('#job_title').on('input propertychange paste change', function(e) {
  $('#job_title_id').val(this.value);
});

$('#unit').on('input propertychange paste change', function(e) {
  $('#unit_id').val(this.value);
});
*/
