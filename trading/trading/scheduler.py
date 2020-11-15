from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.base import JobLookupError


class TradingScheduler:
    scheduler = BackgroundScheduler()

    @classmethod
    def start(cls):
        cls.scheduler.start()

    @classmethod
    def shutdown(cls):
        cls.scheduler.shutdown()

    @classmethod
    def add_job(cls, job_id):
        cls.scheduler.add_job()

    @classmethod
    def kill_job(cls, job_id):
        try:
            cls.scheduler.remove_job(job_id)
        except JobLookupError as err:
            print('fail to stop scheduler')
