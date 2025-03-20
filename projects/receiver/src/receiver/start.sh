#! /bin/bash
uvicorn server:app --host 0.0.0.0 --port ${PORT:-8000} --log-level critical --workers 4
 
