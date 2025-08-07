test_that("ResourceTracker passing the process ID correctly", {
  tracker <- ResourceTracker$new()
  expect_equal(tracker$pid, Sys.getpid())
  while (tracker$n_samples < 1) {
    Sys.sleep(0.1)
  }
  expect_equal(tracker$n_samples, 1)
  expect_true(is.data.frame(tracker$system_metrics))
  expect_true(is.data.frame(tracker$process_metrics))
  expect_equal(tracker$process_metrics$pid[1], tracker$pid)
})
