from setuptools import setup, find_packages
import es_sync

setup(
    name='py-mysql-elasticsearch-sync',
    version=es_sync.__version__,
    packages=find_packages(),
    url='https://github.com/zhongbiaodev/py-mysql-elasticsearch-sync',
    license='MIT',
    author='Windfarer',
    author_email='windfarer@gmail.com',
    description='MySQL to Elasticsearch sync tool',
    install_requires=[
        'PyMySQL==1.0.2',
        'mysql-replication==0.30',
        'requests==2.26.0',
        'PyYAML==5.3',
        'lxml==4.5.0',
        'future==0.15.2',
    ],
    entry_points={
        'console_scripts': [
            'es-sync=es_sync:start',
        ]
    },
    include_package_data=True
)