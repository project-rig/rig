from setuptools import setup, find_packages

setup(
    name="rig",
    version="0.1.2",
    packages=find_packages(),
    package_data={'rig': ['boot/sark.struct', 'boot/scamp.boot',
                          'binaries/*.aplx']
                  },

    # Metadata for PyPi
    url="https://github.com/project-rig/rig",
    author="The Rig Authors",
    description="A collection of tools for developing SpiNNaker applications",
    license="GPLv2",
    classifiers=[
        "Development Status :: 3 - Alpha",

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

        "Topic :: Software Development :: Libraries",
    ],
    keywords="spinnaker placement routing graph fixed-point",

    # Requirements
    install_requires=["numpy>1.6", "six", "enum34", "sentinel"],

    # Scripts
    entry_points={
        "console_scripts": [
            "rig-boot = rig.scripts.rig_boot:main",
            "rig-power = rig.scripts.rig_power:main",
            "rig-info = rig.scripts.rig_info:main",
        ],
    }
)
