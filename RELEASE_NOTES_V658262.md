# MESFlow v65.8.28

- Add a dedicated Flask `HTTPException` handler.
- Return routing 404/405 directly without passing through the unexpected-error pipeline.
- Do not capture traceback or classify routing misses as system errors.
- Preserve `X-Trace-ID` for support correlation.
