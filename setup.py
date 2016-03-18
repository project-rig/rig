import io
import re
from setuptools import setup, find_packages


def read_file(filename, **kwargs):
    encoding = kwargs.get("encoding", "utf-8")

    with io.open(filename, encoding=encoding) as f:
        return f.read()


def replace_local_hyperlinks(
        text, base_url="https://github.com/project-rig/rig/blob/master/"):
    """Replace local hyperlinks in RST with absolute addresses using the given
    base URL.

    This is used to make links in the long description function correctly
    outside of the repository (e.g. when published on PyPi).

    NOTE: This may need adjusting if further syntax is used.
    """
    def get_new_url(url):
        return base_url + url[2:]

    # Deal with anonymous URLS
    for match in re.finditer(r"^__ (?P<url>\./.*)", text, re.MULTILINE):
        orig_url = match.groupdict()["url"]
        url = get_new_url(orig_url)

        text = re.sub("^__ {}".format(orig_url),
                      "__ {}".format(url), text, flags=re.MULTILINE)

    # Deal with named URLS
    for match in re.finditer(r"^\.\. _(?P<identifier>[^:]*): (?P<url>\./.*)",
                             text, re.MULTILINE):
        identifier = match.groupdict()["identifier"]
        orig_url = match.groupdict()["url"]
        url = get_new_url(orig_url)

        text = re.sub(
            "^\.\. _{}: {}".format(identifier, orig_url),
            ".. _{}: {}".format(identifier, url),
            text, flags=re.MULTILINE)

    # Deal with image URLS
    for match in re.finditer(r"^\.\. image:: (?P<url>\./.*)",
                             text, re.MULTILINE):
        orig_url = match.groupdict()["url"]
        url = get_new_url(orig_url)

        text = text.replace(".. image:: {}".format(orig_url),
                            ".. image:: {}".format(url))

    return text

with open("rig/version.py", "r") as f:
    exec(f.read())

setup(
    name="rig",
    version=__version__,
    packages=find_packages(),
    package_data={'rig': ['boot/sark.struct', 'boot/scamp.boot',
                          'binaries/*.aplx']
                  },

    # Metadata for PyPi
    url="https://github.com/project-rig/rig",
    author="The Rig Authors",
    description="A collection of tools for developing SpiNNaker applications",
    long_description = replace_local_hyperlinks(read_file("README.rst")),
    license="GPLv2",
    classifiers=[
        "Intended Audience :: Developers",
        "Intended Audience :: Science/Research",

        "License :: OSI Approved :: GNU General Public License v2 (GPLv2)",

        "Operating System :: POSIX :: Linux",
        "Operating System :: Microsoft :: Windows",
        "Operating System :: MacOS",

        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.4",
        "Programming Language :: Python :: 3.5",

        "Topic :: Software Development :: Libraries",
    ],
    keywords="spinnaker placement routing graph fixed-point",

    # Requirements
    install_requires=["numpy>1.6", "six", "sentinel", "pytz", "enum-compat"],

    # Scripts
    entry_points={
        "console_scripts": [
            "rig-boot = rig.scripts.rig_boot:main",
            "rig-power = rig.scripts.rig_power:main",
            "rig-info = rig.scripts.rig_info:main",
            "rig-discover = rig.scripts.rig_discover:main",
            "rig-iobuf = rig.scripts.rig_iobuf:main",
            "rig-ps = rig.scripts.rig_ps:main",
            "rig-counters = rig.scripts.rig_counters:main",
        ],
    }
)
