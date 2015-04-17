from setuptools import setup, find_packages
import sys

setup(
    name="rig",
    version="0.0.2.dev",
    packages=find_packages(),

    # Metadata for PyPi
    author="Jonathan Heathcote, Andrew Mundy",
    description="A set of libraries for mapping problems to SpiNNaker",
    license="GPLv2",

    # Requirements
    install_requires=["numpy>1.6", "six", "enum34", "sentinel"],
    tests_require=["pytest>=2.6", "pytest-cov", "mock", "toposort"],

    # Scripts
    entry_points={
        "console_scripts": [
            "rig-boot = rig.scripts.rig_boot:main",
            "rig-power = rig.scripts.rig_power:main",
            "rig-info = rig.scripts.rig_info:main",
        ],
    }
)
