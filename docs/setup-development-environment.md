# Setup Development Environment

2. [Install and activate mise](https://mise.jdx.dev/installing-mise.html)

3. Install Docker Desktop (or Docker Engine on Linux)
   
3. Activate the virtual environment:
   ```bash
   asdf install
   poetry env use $(asdf current python --no-header | awk -F ' ' '{ print $2 }')
   poetry install

   # (Optional) To avoid calling poetry run every time, you can activate the virtualenv in your shell:
   eval $(poetry env activate)

   # To recreate the virtualenv from scratch:
   poetry env remove --all
   ```