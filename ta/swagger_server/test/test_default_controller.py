# coding: utf-8

from __future__ import absolute_import

from swagger_server.models.inline_response200 import InlineResponse200
from swagger_server.models.inline_response2001 import InlineResponse2001
from swagger_server.models.inline_response2002 import InlineResponse2002
from swagger_server.models.inline_response2003 import InlineResponse2003
from swagger_server.models.inline_response400 import InlineResponse400
from swagger_server.models.inline_response4001 import InlineResponse4001
from swagger_server.models.inline_response4002 import InlineResponse4002
from swagger_server.models.inline_response4003 import InlineResponse4003
from swagger_server.models.parameters import Parameters
from swagger_server.models.parameters1 import Parameters1
from swagger_server.models.parameters2 import Parameters2
from . import BaseTestCase
from six import BytesIO
from flask import json


class TestDefaultController(BaseTestCase):
    """ DefaultController integration test stubs """

    def test_action_observe_get(self):
        """
        Test case for action_observe_get

        
        """
        response = self.client.open('/action/observe',
                                    method='GET')
        self.assert200(response, "Response body is : " + response.data.decode('utf-8'))

    def test_action_start_post(self):
        """
        Test case for action_start_post

        
        """
        response = self.client.open('/action/start',
                                    method='POST')
        self.assert200(response, "Response body is : " + response.data.decode('utf-8'))

    def test_perturb_battery_post(self):
        """
        Test case for perturb_battery_post

        
        """
        Parameters = Parameters2()
        response = self.client.open('/perturb/battery',
                                    method='POST',
                                    data=json.dumps(Parameters),
                                    content_type='application/json')
        self.assert200(response, "Response body is : " + response.data.decode('utf-8'))

    def test_perturb_place_obstacle_post(self):
        """
        Test case for perturb_place_obstacle_post

        
        """
        Parameters = Parameters()
        response = self.client.open('/perturb/place_obstacle',
                                    method='POST',
                                    data=json.dumps(Parameters),
                                    content_type='application/json')
        self.assert200(response, "Response body is : " + response.data.decode('utf-8'))

    def test_perturb_remove_obstacle_post(self):
        """
        Test case for perturb_remove_obstacle_post

        
        """
        Parameters = Parameters1()
        response = self.client.open('/perturb/remove_obstacle',
                                    method='POST',
                                    data=json.dumps(Parameters),
                                    content_type='application/json')
        self.assert200(response, "Response body is : " + response.data.decode('utf-8'))


if __name__ == '__main__':
    import unittest
    unittest.main()
