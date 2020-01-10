from __future__ import absolute_import
from datetime import date, datetime  # noqa: F401

from typing import List, Dict  # noqa: F401

from swagger_server.models.base_model_ import Model
from swagger_server import util

class InternalStatusResponse200(Model):

    def __init__(self, success: bool=None):
        self.swagger_types = {
            'success': bool
        }

        self.attribute_map = {
            'success' : 'success'
        }

        self._success = success

    @classmethod
    def from_dict(cls, dikt) -> 'InternalStatusResponse200':
        return util.deserialize_model(dikt, cls)

    @property
    def success(self):
        return self._success

    @success.setter
    def success(self, success : bool):
        self._success = succes
    