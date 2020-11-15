from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.background import BackgroundScheduler


class BotScheduler(object):
    def __init__(self):
        self.scheduler = BackgroundScheduler()

    def start(self):
        self.scheduler.start()

    def shutdown(self):
        self.scheduler.shutdown()

    def remove_job(self, job_id):
        try:
            self.scheduler.remove_job(job_id)
        except JobLookupError as e:
            print('Fail to remove job')

    def add_job(self, job_id, func, minute, second, kwargs=None):
        self.scheduler.add_job(func, 'cron', id=job_id, minute=minute, second=second, kwargs=kwargs)
