#! /usr/bin/env python

import calendar
import functools
import os
import sys
import re
import getopt
import datetime
import urllib2
# import jira
# from jira.client import JiraClient
import pivotalTracker
from pivotalTracker.client import PivotalTrackerClient

from youtrack import Issue, YouTrackException, Comment, Link, WorkItem
import youtrack
from youtrack.connection import Connection
from youtrack.importHelper import create_bundle_safe

jt_fields = []

_debug = os.environ.get('DEBUG')


def usage():
    print """
Usage:
    %s [OPTIONS] p_api_key p_project_id y_url y_user y_pass

The script imports issues from Pivotal Tracker to YouTrack.
By default it imports issues and all attributes like attachments, labels, links.
This behaviour can be changed by passing import options -i, -a, -r and -t.

Arguments:
    p_api_key     Pivotal Tracker user
    p_project_id  Pivotal Tracker project id to import

    y_url         YouTrack URL
    y_user        YouTrack user
    y_pass        YouTrack user's password
    y_project     YouTrack main project to import to

Options:
    -h,  Show this help and exit
    
    -i,  Import issues
    -a,  Import attachments
    -t,  Import labels (convert to YT tags)
    
    -r,  Replace old attachments with new ones (remove and re-import)
    
    -m,  Comma-separated list of field mappings.
         Mapping format is PT_FIELD_NAME:YT_FIELD_NAME@FIELD_TYPE
    -M,  Comma-separated list of field value mappings.
         Mapping format is YT_FIELD_NAME:PT_FIELD_VALUE=YT_FIELD_VALUE[;...]
""" % os.path.basename(sys.argv[0])


# Primary import options
FI_ISSUES = 0x01
FI_ATTACHMENTS = 0x02
FI_LABELS = 0x08

# Secondary import options (from 0x80)
FI_REPLACE_ATTACHMENTS = 0x80


def main():
    flags = 0
    field_mappings = dict()
    value_mappings = dict()
    try:
        opts, args = getopt.getopt(sys.argv[1:], 'harltim:M:')
        for opt, val in opts:
            if opt == '-h':
                usage()
                sys.exit(0)
            elif opt == '-i':
                flags |= FI_ISSUES
            elif opt == '-a':
                flags |= FI_ATTACHMENTS
            elif opt == '-r':
                flags |= FI_REPLACE_ATTACHMENTS
            elif opt == '-t':
                flags |= FI_LABELS
            elif opt == '-m':
                for mapping in val.split(','):
                    m = re.match(r'^([^:]+):([^@]+)@(.+)$', mapping)
                    if not m:
                        raise ValueError('Bad field mapping (skipped): %s' % mapping)
                    pt_name, yt_name, field_type = m.groups()
                    field_mappings[pt_name.lower()] = (yt_name.lower(), field_type)
            elif opt == '-M':
                for mapping in val.split(','):
                    m = re.match(r'^([^:]+):(.+)$', mapping)
                    if not m:
                        raise ValueError('Bad field mapping (skipped): %s' % mapping)
                    field_name, v_mappings = m.groups()
                    field_name = field_name.lower()
                    for vm in v_mappings.split(';'):
                        m = re.match(r'^([^=]+)=(.+)$', vm)
                        if not m:
                            raise ValueError('Bad field mapping (skipped): %s' % vm)
                        pt_value, yt_value = m.groups()
                        if field_name not in value_mappings:
                            value_mappings[field_name] = dict()
                        value_mappings[field_name][pt_value.lower()] = yt_value
    except getopt.GetoptError, e:
        print e
        usage()
        sys.exit(1)
    if len(args) < 6:
        print 'Not enough arguments'
        usage()
        sys.exit(1)

    if not flags & 0x7F:
        flags |= FI_ISSUES | FI_ATTACHMENTS | FI_LABELS
    p_api_key, p_project_id, y_url, y_login, y_password, y_project = args[:6]

    if not value_mappings:
        value_mappings = pivotalTracker.VALUE_MAPPINGS

    # projects = []
    # for project in args[6:]:
    #     m = re.match(
    #         r'^(?P<pid>[^,]+)(?:,(?P<n1>\d+)(?::(?P<n2>\d+))?)?$', project)
    #     if m:
    #         m = m.groupdict()
    #         start = 1
    #         end = 0
    #         if m.get('n2') is not None:
    #             start = int(m['n1'])
    #             end = int(m['n2'])
    #         elif m.get('n1') is not None:
    #             start = 1
    #             end = int(m['n1'])
    #         if end and end < start:
    #             raise ValueError('Bad argument => %s' % project)
    #         projects.append((m['pid'].upper(), start, end))
    #     else:
    #         raise ValueError('Bad argument => %s' % project)

    pivotalTracker2youtrack(p_api_key, p_project_id,
                            y_url, y_login, y_password, y_project,
                            flags, field_mappings, value_mappings)


def pivotalTracker2youtrack(source_api_key, source_project_id,
                            target_url, target_login, target_password, target_project,
                            flags, field_mappings, value_mappings):
    print 'source_api_key   : ' + source_api_key
    print 'source_project_id : ' + source_project_id
    print 'target_url   : ' + target_url
    print 'target_login : ' + target_login
    print 'target_password : ' + target_password
    print 'target_project: ' + target_project

    source = PivotalTrackerClient(source_api_key, source_project_id)
    # Todo Sean: fix
    target = Connection(target_url, target_login, target_password, None,
                        "perm:c2Vhbm1jbg==.VG9rZW4=.a3KymGhp2z5Gt5JcaGgv1DiRvXBTVu")

    # for project in projects:
    #     project_id, start, end = project
    # try:
    #     target.createProjectDetailed(project_id, project_id, '', target_login)
    # except YouTrackException:
    #     pass

    limit = 1
    # start, end = [0, 0]
    total_issues = source.get_issue_count()

    # offset = 0
    processed_issues = 0

    while processed_issues < total_issues:
        # Get issues
        issues = source.get_issues(processed_issues, limit)

        issues2import = []

        # Deal with each issue
        for issue in issues:
            # Are we importing issues or just comments / tags?
            if flags & FI_ISSUES:
                issues2import.append(to_yt_issue(target, issue, target_project, field_mappings, value_mappings))
            print(issues2import)

        # if issues2import:
        #     target.importIssues(target_project, '%s assignees' % target_project, issues2import)

        processed_issues += limit
        break

    return
    # if processed_issues >= total_issues:
    #     break

    # _end = start + chunk_size - 1
    # if end and _end > end:
    #     _end = end
    # if start > _end:
    #     break
    # stories?offset=0&limit=0&envelope=true

    # print 'Processing issues: %s [%d .. %d]' % (source_project_id, start, _end)
    # try:
    #     pivotal_issues = source.get_issues(start, _end)
    #     start += chunk_size
    #     # if not (pivotal_issues or end):
    #     #     break
    #     # Filter out moved issues
    #     pivotal_issues = [issue for issue in pivotal_issues
    #                       if issue['key'].startswith('%s-' % project_id)]
    #     if flags & FI_ISSUES:
    #         issues2import = []
    #         for issue in pivotal_issues:
    #             issues2import.append(
    #                 to_yt_issue(target, issue, project_id,
    #                             field_mappings, value_mappings))
    #         # if not issues2import:
    #         #     continue
    #         target.importIssues(
    #             project_id, '%s assignees' % project_id, issues2import)
    # # except YouTrackException, e:
    # #     print e
    # #     continue
    # for issue in pivotal_issues:
    #     if flags & FI_LABELS:
    #         process_labels(target, issue)
    #     if flags & FI_ATTACHMENTS:
    #         process_attachments(source, target, issue,
    #                             flags & FI_REPLACE_ATTACHMENTS > 0)


def to_yt_issue(target, issue, project_id,
                fields_mapping=None, value_mappings=None):
    yt_issue = Issue()
    # yt_issue['comments'] = []
    yt_issue.numberInProject = issue['id'] #[(issue['id'].find('-') + 1):]
    for field, value in issue.items():
        if value is None:
            continue
        if fields_mapping and field.lower() in fields_mapping:
            field_name, field_type = fields_mapping[field.lower()]
        else:
            field_name = get_yt_field_name(field)
            field_type = get_yt_field_type(field_name)
        # if field_name == 'comment':
        #     for comment in value['comments']:
        #         yt_comment = Comment()
        #         yt_comment.text = comment['body']
        #         comment_author_name = "guest"
        #         if 'author' in comment:
        #             comment_author = comment['author']
        #             create_user(target, comment_author)
        #             comment_author_name = comment_author['name']
        #         yt_comment.author = comment_author_name.replace(' ', '_')
        #         yt_comment.created = to_unix_date(comment['created'])
        #         yt_comment.updated = to_unix_date(comment['updated'])
        #         yt_issue['comments'].append(yt_comment)

        if (field_name is not None) and (field_type is not None):
            if isinstance(value, list) and len(value):
                yt_issue[field_name] = []
                for v in value:
                    if isinstance(v, dict):
                        v['name'] = get_yt_field_value(field_name, v['name'], value_mappings)
                    else:
                        v = get_yt_field_value(field_name, v, value_mappings)

                    create_value(target, v, field_name, field_type, project_id)
                    yt_issue[field_name].append(get_value_presentation(field_type, v))
            else:
                # if field_name.lower() == 'estimation':
                #     if field_type == 'period':
                #         value = int(int(value) / 60)
                #     elif field_type == 'integer':
                #         value = int(int(value) / 3600)
                if isinstance(value, int):
                    value = str(value)
                if len(value):
                    if isinstance(value, dict):
                        value['name'] = get_yt_field_value(field_name, value['name'], value_mappings)
                    else:
                        value = get_yt_field_value(field_name, value, value_mappings)

                    create_value(target, value, field_name, field_type, project_id)
                    yt_issue[field_name] = get_value_presentation(field_type, value)
        elif _debug:
            print 'DEBUG: unclassified field', field_name
    return yt_issue


def get_yt_field_name(pivotal_name):
    if pivotal_name in pivotalTracker.FIELD_NAMES:
        return pivotalTracker.FIELD_NAMES[pivotal_name]
    return pivotal_name


def get_yt_field_type(yt_name):
    result = pivotalTracker.FIELD_TYPES.get(yt_name)
    if result is None:
        result = youtrack.EXISTING_FIELD_TYPES.get(yt_name)
    return result


def get_yt_field_value(field_name, pivotal_value, value_mappings):
    new_value = pivotal_value
    if isinstance(field_name, unicode):
        field_name = field_name.encode('utf-8')
    if isinstance(pivotal_value, unicode):
        pivotal_value = pivotal_value.encode('utf-8')
    try:
        new_value = value_mappings[field_name.lower()][pivotal_value.lower()]
    except KeyError:
        pass

    return new_value


def create_value(target, value, field_name, field_type, project_id):
    # if field_type.startswith('user'):
    #     create_user(target, value)
    #     value['name'] = value['name'].replace(' ', '_')
    if field_name in pivotalTracker.EXISTING_FIELDS:
        return
    if field_name.lower() not in [field.name.lower() for field in target.getProjectCustomFields(project_id)]:
        if field_name.lower() not in [field.name.lower() for field in target.getCustomFields()]:
            target.createCustomFieldDetailed(field_name, field_type, False, True, False, {})
        if field_type in ['string', 'date', 'integer', 'period']:
            try:
                target.createProjectCustomFieldDetailed(project_id, field_name, "No " + field_name)
            except YouTrackException, e:
                if e.response.status == 409:
                    print e
                else:
                    raise e
        else:
            bundle_name = "%s: %s" % (project_id, field_name)
            create_bundle_safe(target, bundle_name, field_type)
            try:
                target.createProjectCustomFieldDetailed(project_id, field_name, "No " + field_name,
                                                        {'bundle': bundle_name})
            except YouTrackException, e:
                if e.response.status == 409:
                    print e
                else:
                    raise e
    if field_type in ['string', 'date', 'integer', 'period']:
        return
    project_field = target.getProjectCustomField(project_id, field_name)
    bundle = target.getBundle(field_type, project_field.bundle)
    try:
        target.addValueToBundle(bundle, re.sub(r'[<>/]', '_', get_value_presentation(field_type, value)))
    except YouTrackException:
        pass


def to_unix_date(time_string, truncate=False):
    tz_diff = 0
    if len(time_string) == 10:
        dt = datetime.datetime.strptime(time_string, '%Y-%m-%d')
    else:
        m = re.search('(Z|([+-])(\d\d):?(\d\d))$', time_string)
        if m:
            tzm = m.groups()
            time_string = time_string[0:-len(tzm[0])]
            if tzm[0] != 'Z':
                tz_diff = int(tzm[2]) * 60 + int(tzm[3])
                if tzm[1] == '-':
                    tz_diff = -tz_diff
        time_string = re.sub('\.\d+$', '', time_string).replace('T', ' ')
        dt = datetime.datetime.strptime(time_string, '%Y-%m-%d %H:%M:%S')
    epoch = calendar.timegm(dt.timetuple()) + tz_diff
    if truncate:
        epoch = int(epoch / 86400) * 86400
    return str(epoch * 1000)


def get_value_presentation(field_type, value):
    if field_type == 'date':
        return to_unix_date(value)
    if field_type == 'integer' or field_type == 'period':
        return str(value)
    if field_type == 'string':
        return value
    if 'name' in value:
        return value['name']
    if 'value' in value:
        return value['value']

    # Todo: Probably don't just return value, check for custom field types etc.
    return value


if __name__ == '__main__':
    main()
