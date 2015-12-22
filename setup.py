from setuptools import setup, find_packages
import src

setup(
    name='py-mysql-elasticsearch-sync',
    version=src.__version__,
    packages=find_packages(),
    url='https://github.com/zhongbiaodev/py-mysql-elasticsearch-sync',
    license='MIT',
    author='Windfarer',
    author_email='windfarer@gmail.com',
    description='MySQL to Elasticsearch sync tool',
    install_requires=[
        'mysql-replication',
        'requests',
        'pyyaml',
        'lxml',
    ],
    entry_points={
        'console_scripts': [
            'es-sync=:run',
        ]
    },
    include_package_data=True
)