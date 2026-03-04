from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as f:
    long_description = f.read()

with open("requirements.txt", "r", encoding="utf-8") as f:
    requirements = [
        line.strip()
        for line in f
        if line.strip() and not line.startswith("#")
    ]

setup(
    name="vlc-zoom-crop",
    version="1.0.0",
    author="Cleo",
    description="VLC Intelligent Crop & Zoom Plugin with high-quality upscaling",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Stonesetter/vlc-zoom-crop-addon",
    py_modules=["vlc_upscaler", "video_processor"],
    python_requires=">=3.8",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "vlc-upscaler=vlc_upscaler:main",
            "vlc-video-processor=video_processor:main",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Topic :: Multimedia :: Video",
    ],
)
