"""DriftGuard SDK — ML Model Drift Monitoring."""

from setuptools import setup, find_packages

setup(
    name="driftguard",
    version="1.0.0",
    description="Python SDK for DriftGuard ML Model Monitoring & Drift Detection",
    long_description=open("README.md").read() if __import__("os").path.exists("README.md") else "",
    long_description_content_type="text/markdown",
    author="DriftGuard",
    author_email="sdk@driftguard.io",
    url="https://github.com/driftguard/driftguard-sdk",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "httpx>=0.25.0",
    ],
    extras_require={
        "numpy": ["numpy>=1.24.0"],
        "dev": [
            "pytest>=7.0",
            "pytest-asyncio>=0.21",
            "pytest-cov>=4.0",
        ],
    },
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
    keywords="ml monitoring drift detection machine-learning mlops",
)
