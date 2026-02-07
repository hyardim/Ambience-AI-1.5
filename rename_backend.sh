#!/bin/bash

# 1. Rename the folder
mv backend/app backend/src

# 2. Update Dockerfile to point to 'src' instead of 'app'
# The -i '' is required for Mac sed
sed -i '' 's/app\.main:app/src.main:app/g' backend/Dockerfile
sed -i '' 's/COPY app/COPY src/g' backend/Dockerfile

echo "Done! Renamed app to src and updated Dockerfile."
