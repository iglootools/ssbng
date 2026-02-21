# Releasing and Publishing

The build uses the [poetry-dynamic-versioning](https://github.com/mtkennerly/poetry-dynamic-versioning) plugin 
to automatically set the version based on git tags. 

The following GitHub workflows are set up to automate the release and publishing process:
1. The `release` workflow takes care of pushing a tag based on conventional commits and creating the Github release.
   This workflow uses the [github-tag](https://github.com/marketplace/actions/github-tag) action
2. The `publish` workflow takes care of publishing the package to PyPI
   This workflow uses the [pypa/gh-action-pypi-publish](https://github.com/pypa/gh-action-pypi-publish) action
