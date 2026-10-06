from .cbr import CbrFx, CbrKeyRate
from .emiss import EmissProducer, EmissRetail
from .openmeteo import OpenMeteo

SOURCES = {cls.name: cls for cls in (EmissRetail, EmissProducer, CbrFx, CbrKeyRate, OpenMeteo)}
