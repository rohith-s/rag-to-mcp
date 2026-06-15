# skills.md - UC-0A Complaint Classifier

skills:
  - name: classify_complaint
    description: >
      Classify one complaint row into the fixed UC-0A category and priority
      schema, returning a reason and review flag for dashboard ingestion.
    input: >
      A dict representing one CSV row with complaint_id, description,
      location, city, ward, and related metadata fields.
    output: >
      A dict with complaint_id, category, priority, reason, and flag.
      Category and priority must use only allowed schema values.
    error_handling: >
      Missing, vague, or very short descriptions return category Other,
      priority Standard unless a severity keyword is present, and
      flag NEEDS_REVIEW. The reason explains that no confident category
      matched the complaint text.

  - name: batch_classify
    description: >
      Classify every valid row in a city test CSV and write a results CSV.
    input: >
      Path to a test CSV file such as data/city-test-files/test_pune.csv.
    output: >
      Path to a results CSV file such as uc-0a/results_pune.csv containing
      complaint_id, category, priority, reason, and flag columns.
    error_handling: >
      Malformed rows are logged to stderr and skipped. Processing continues
      for the remaining rows, and the output file is still written.
