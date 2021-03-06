# coding: utf-8

from __future__ import absolute_import
from datetime import date, datetime  # noqa: F401

from typing import List, Dict  # noqa: F401

from swagger_server.models.base_model_ import Model
from swagger_server import util


class BatteryParams(Model):
    """NOTE: This class is auto generated by the swagger code generator program.

    Do not edit the class manually.
    """

    def __init__(self, charge: float=None):  # noqa: E501
        """BatteryParams - a model defined in Swagger

        :param charge: The charge of this BatteryParams.  # noqa: E501
        :type charge: float
        """
        self.swagger_types = {
            'charge': float
        }

        self.attribute_map = {
            'charge': 'charge'
        }

        self._charge = charge

    @classmethod
    def from_dict(cls, dikt) -> 'BatteryParams':
        """Returns the dict as a model

        :param dikt: A dict.
        :type: dict
        :return: The BatteryParams of this BatteryParams.  # noqa: E501
        :rtype: BatteryParams
        """
        return util.deserialize_model(dikt, cls)

    @property
    def charge(self) -> float:
        """Gets the charge of this BatteryParams.

        the level to which the battery should be set, in mWh. cannot be more than the maximum charge for the power model specified in the THs response to `/ready`.  # noqa: E501

        :return: The charge of this BatteryParams.
        :rtype: float
        """
        return self._charge

    @charge.setter
    def charge(self, charge: float):
        """Sets the charge of this BatteryParams.

        the level to which the battery should be set, in mWh. cannot be more than the maximum charge for the power model specified in the THs response to `/ready`.  # noqa: E501

        :param charge: The charge of this BatteryParams.
        :type charge: float
        """
        if charge is None:
            raise ValueError("Invalid value for `charge`, must not be `None`")  # noqa: E501
        if charge is not None and charge < 0:  # noqa: E501
            raise ValueError("Invalid value for `charge`, must be a value greater than or equal to `0`")  # noqa: E501

        self._charge = charge
