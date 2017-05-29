import os
import base64
import json
import httplib2
from pivotalTracker import PivotalTrackerException

_debug = os.environ.get('DEBUG')


class PivotalTrackerClient(object):
    def __init__(self, api_key, project_id):
        self._url = "https://www.pivotaltracker.com/services/v5"
        self._project_id = project_id
        self._headers = {
            'X-TrackerToken': api_key
        }
        self._http = httplib2.Http(timeout=10, disable_ssl_certificate_validation=True)
        self._login(api_key, project_id)

    def _rest_url(self):
        return self._url + "/projects/" + self._project_id

    def get_issue_count(self):
        response, content = self._get(self._rest_url() + '/stories?offset=0&limit=0&envelope=true')
        return content['pagination']['total']

    def get_issues(self, offset, limit):
        # issues = []
        response, content = self._get(self._rest_url() + '/stories?offset=' + str(offset) + '&limit=' + str(limit))
        # print(response)
        # print(content)

        # stories?offset=$offset&limit=$limit
        # for i in range(from_id, to_id + 1):
        #     issue = self.get_issue('%s-%d' % (project_key, i))
        #     if issue is not None:
        #         issues.append(issue)
        return content

    def _post(self, url, body):
        headers = self._headers.copy()
        headers['Content-Type'] = 'application/json'
        json_body = json.dumps(body)
        headers['Content-Length'] = str(len(json_body))
        response, content = self._http.request(url, "POST", json_body, headers)
        if response.status != 200:
            raise PivotalTrackerException(response)
        return response, json.loads(content)

    def _get(self, url):
        if _debug:
            print "DEBUG: _get %s" % url
        response, content = self._http.request(url, headers=self._headers.copy())
        if _debug:
            print "DEBUG: response: %d" % response.status
            print "DEBUG: content: %s" % content
        return response, json.loads(content)

    ################################

    # def get_issue_link_types(self):
    #     response, content = self._get(self._rest_url() + '/issueLinkType')
    #     return content

    def get_project_by_id(self, key):
        response, content = self._get(self._rest_url() + "/project/" + key)
        return content

    # def get_issues(self, project_key, from_id, to_id):
    #     issues = []
    #     for i in range(from_id, to_id + 1):
    #         issue = self.get_issue('%s-%d' % (project_key, i))
    #         if issue is not None:
    #             issues.append(issue)
    #     return issues

    def get_issue(self, issue_id):
        response, content = self._get(self._rest_url() + "/issue/" + issue_id)
        if response.status == 200:
            return content
        print "Can't get issue " + issue_id

    # def get_worklog(self, issue_id):
    #     response, content = self._get(self._rest_url() + "/issue/" + issue_id + '/worklog')
    #     if response.status == 200:
    #         return content
    #     print "Can't get worklog for issue " + issue_id

    def _login(self, login, password):
        # response, content = self._post(self._url + "/auth/1/session", {"username": login, "password": password})
        # self._headers['JSESSIONID'] = content['session']['value']
        auth = base64.encodestring(login + ':' + password)
        self._headers['Authorization'] = 'Basic ' + auth
