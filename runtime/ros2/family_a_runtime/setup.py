from setuptools import find_packages, setup


setup(
    name="family_a_runtime",
    version="0.1.0",
    packages=find_packages(),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/family_a_runtime"]),
        ("share/family_a_runtime", ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Family A maintainers",
    maintainer_email="noreply@example.invalid",
    description="Family A Thor SITL runtime nodes",
    license="BSD-3-Clause",
    entry_points={
        "console_scripts": [
            "telemetry_sidecar = family_a_runtime.telemetry_sidecar:main",
            "offboard_controller = family_a_runtime.offboard_controller:main",
            "external_mode_requester = family_a_runtime.external_mode_requester:main",
            "manual_requester = family_a_runtime.manual_requester:main",
            "safety_supervisor = family_a_runtime.safety_supervisor:main",
        ]
    },
)
