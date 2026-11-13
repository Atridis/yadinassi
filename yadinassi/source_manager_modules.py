"""Source manager namespaces exposing BSL exports, not implicit persistence."""
import weakref
from .values import BSLObject

MANAGER_NAMES = {
    'catalogs': 'Catalog', 'справочники': 'Catalog',
    'documents': 'Document', 'документы': 'Document',
    'informationregisters': 'InformationRegister', 'регистрысведений': 'InformationRegister',
    'accumulationregisters': 'AccumulationRegister', 'регистрынакопления': 'AccumulationRegister',
    'accountingregisters': 'AccountingRegister', 'регистрыбухгалтерии': 'AccountingRegister',
    'calculationregisters': 'CalculationRegister', 'регистрырасчета': 'CalculationRegister',
    'chartsofcharacteristictypes': 'ChartOfCharacteristicTypes', 'планывидовхарактеристик': 'ChartOfCharacteristicTypes',
    'chartsofaccounts': 'ChartOfAccounts', 'планысчетов': 'ChartOfAccounts',
    'chartsofcalculationtypes': 'ChartOfCalculationTypes', 'планывидоврасчета': 'ChartOfCalculationTypes',
    'businessprocesses': 'BusinessProcess', 'бизнеспроцессы': 'BusinessProcess',
    'tasks': 'Task', 'задачи': 'Task',
    'exchangeplans': 'ExchangePlan', 'планыобмена': 'ExchangePlan',
    'reports': 'Report', 'отчеты': 'Report',
    'dataprocessors': 'DataProcessor', 'обработки': 'DataProcessor',
}


class SourceManagers(BSLObject):
    def __init__(self, application, family):
        self._application = weakref.ref(application)
        self._family = family

    def authorize(self, caller):
        app = self._application()
        if app is None:
            raise ValueError('source manager belongs to a closed application')
        app.require_manager_context(caller)
        return app

    def member(self, caller, name):
        app = self.authorize(caller)
        if type(name) is not str:
            raise TypeError("source manager name must be a string")
        return app.manager_module(self._family, name, caller)
