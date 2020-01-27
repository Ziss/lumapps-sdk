from setuptools import setup, find_packages
from lumapps.api import __version__, __pypi_packagename__


with open("README.rst", "r") as f:
    readme = f.read()
setup(
    name=__pypi_packagename__,
    version=__version__,
    author="LumApps",
    url="https://github.com/lumapps/lumapps-sdk",
    packages=find_packages(exclude=["documentation", "tests", "examples"]),
    include_package_data=True,
    license="MIT",
    description="LumApps SDK for Python",
    long_description=readme,
    long_description_content_type="text/x-rst",
    install_requires=["requests==2.22.*", "Authlib==0.13.*"],
    python_requires=">=3.6",
    keywords="lumapps sdk",
    classifiers=[
        "License :: OSI Approved :: MIT License",
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
    ],
    project_urls={
        "Documentation": "https://lumapps.github.io/lumapps-sdk/",
        "Source": "https://github.com/lumapps/lumapps-sdk",
        "Issues": "https://github.com/lumapps/lumapps-sdk/issues",
        "CI": "https://circleci.com/gh/lumapps/lumapps-sdk",
    },
    entry_points={"console_scripts": ["lac=lumapps.api.cli:main"]},
)
