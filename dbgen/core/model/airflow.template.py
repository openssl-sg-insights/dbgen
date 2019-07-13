# External imports
from typing import Any
import psycopg2 # type: ignore
from psycopg2.extras import DictCursor # type: ignore
from airflow import DAG # type: ignore
from airflow.operators.python_operator import PythonOperator # type: ignore
from datetime import datetime

# Internal Imports


# Written by {{ user }}

# Define Callables for operators
{% for operator,operator_def in operators.items() %}
def f_{{ operator }}() -> None:
    {{ operator_def }}
{% endfor %}

# Define DAG
default_args ={
    'owner'             : '{{ user }}',
    'start_date'        : datetime.strptime('{{ date }}','%Y-%m-%d'),
    'retries'           : 1,
    'backfill'          : False,
    'catchup'           : False
}

default_args.update({{ dag_args }})
with DAG('{{ modelname }}',schedule_interval = '{{ schedule_interval }}', default_args = default_args) as dag:
    {% for operator in operators.keys() %}
    {{operator}} = PythonOperator(task_id = '{{operator}}', python_callable = f_{{ operator }})
    {% endfor %}

# Add dependencies
{% for child,parent in deps %}
{{ parent }}.set_upstream({{ child}})
{% endfor %}

if __name__ == '__main__':
{% for operator in operators.keys() %}
    f_{{ operator }}()
{% endfor %}