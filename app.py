#!/usr/bin/env python
import os
import json
from flask import (Flask, render_template, request, session, url_for, redirect,
                    flash, abort)

import logic as l

app = Flask(__name__)
app.secret_key = os.environ['FLASK_SECRET_KEY']

@app.template_filter('date')
def date_filter(d):
    return d.strftime('%b-%-d %I:%M')

"""
Account Silliness
""" 
_ADMIN_EMAILS = set(json.loads(os.environ['ADMIN_EMAILS']))
@app.before_request
def security_check():
    request.user = l.get_user(session.get('userid'))
   
    path = request.path
    if (request.user and path.startswith('/admin') 
            and request.user.email not in _ADMIN_EMAILS):
        abort(403)

    if request.user:
        return

    for prefix in ('/static', '/user', '/feedback'):
        if path.startswith(prefix):
            return

    return redirect(url_for('login'))

@app.route('/user/login/')
def login():
    return render_template('login.html')

@app.route('/user/login/', methods=['POST'])
def login_post():
    uid = l.check_pw(request.values.get('email'),
                        request.values.get('pw'))
    if not uid:
        flash('Bad email or password.')
        return redirect(url_for('login'))
    user = l.get_user(uid)
    if not user.approved:
        flash('You have not yet been approved.')
        return redirect(url_for('login'))
    session['userid'] = uid
    return redirect('/')

@app.route('/user/new/')
def new_user():
    return render_template('new_user.html')

@app.route('/user/new/', methods=['POST'])
def new_user_post():
    uid = l.add_user(request.values.get('email'),
                       request.values.get('name'),
                         request.values.get('pw'))
    flash('You will be able to log in after your account is approved!')
    return redirect(url_for('login'))

@app.route('/user/logout/')
def logout():
    session.clear()
    return redirect(url_for('login'))

"""
Admin
"""
@app.route('/admin/')
def admin_menu():
    return render_template('admin_page.html')

@app.route('/admin/users/')
def list_users():
    return render_template('user_list.html', users=l.list_users())

@app.route('/admin/users/<int:uid>/approve/', methods=['POST'])
def approve_user(uid):
    l.approve_user(uid)
    user = l.get_user(uid)
    flash('Approved user {}'.format(user.email))
    return redirect(url_for('list_users'))

@app.route('/admin/reasons/')
def list_reasons():
    return render_template('reasons.html', reasons=l.get_reasons())

@app.route('/admin/reasons/', methods=['POST'])
def add_reason():
    text = request.values.get('text')
    l.add_reason(text)
    flash('Added reason "{}"'.format(text))
    return redirect(url_for('list_reasons'))


"""
User State
"""
@app.route('/votes/')
def show_votes():
    return render_template('my_votes.html', votes=l.get_my_votes(request.user.id))

@app.route('/bookmarks/')
def show_bookmarks():
    return render_template('bookmarks.html', bookmarks=l.get_bookmarks(request.user.id))

@app.route('/unread/')
def show_unread():
    return render_template('unread.html', unread=l.get_unread(request.user.id)) 

"""
Kittendome Action
"""
@app.route('/kitten/<int:id>/')
def kitten(id):
    proposal = l.get_proposal(id)
    if not proposal:
        abort(404)

    if request.user.email in (x.email.lower() for x in proposal.authors):
        abort(404)

    unread = l.is_unread(request.user.id, id)
    discussion = l.get_discussion(id)

    votes = l.get_votes(id)
    reasons = l.get_reasons()
    progress = l.kitten_progress()
    authors = ', '.join(x.name for x in proposal.authors)
    bookmarked = l.has_bookmark(request.user.id, id)

    existing_vote = None
    if request.user.id in [x.voter for x in votes]:
        existing_vote = [x for x in votes if x.voter == request.user.id][0]

    return render_template('kitten_proposal.html', proposal=proposal,
                            votes=votes, discussion=discussion,
                            reasons=reasons, progress=progress,
                            authors=authors, bookmarked=bookmarked,
                            existing_vote=existing_vote,
                            unread=unread)

@app.route('/kitten/<int:id>/vote/', methods=['POST'])
def vote(id):
    yea  = request.values.get('vote', None) == 'yea'
    redir = redirect(url_for('kitten', id=id))
    reason = request.values.get('reason', None)
    if not reason or not reason.strip():
        reason = None
    if l.vote(request.user.id, id, yea, reason):
        proposal = l.get_proposal(id)
        flash('You voted "{}" for "{}" #{}'.format('Yea' if yea else 'Nay',
                proposal.title, proposal.id))
        return redirect(url_for('pick'))
    return redir

@app.route('/kitten/<int:id>/comment/', methods=['POST'])
def comment(id):
    comment = request.values.get('comment').strip()
    redir = redirect(url_for('kitten', id=id))
    if not comment:
        flash("Empty comment")
        return redir
    l.add_to_discussion(request.user.id, id, comment, feedback=False)
    return redir

@app.route('/kitten/<int:id>/feedback/', methods=['POST'])
def feedback(id):
    comment = request.values.get('feedback').strip()
    redir = redirect(url_for('kitten', id=id))
    if not comment:
        flash('Empty comment')
        return redir
    l.add_to_discussion(request.user.id, id, comment, feedback=True)
    return redir

@app.route('/kitten/<int:id>/bookmark/add/', methods=['POST'])
def add_bookmark(id):
    l.add_bookmark(request.user.id, id)
    return redirect(url_for('kitten', id=id))

@app.route('/kitten/<int:id>/bookmark/remove/', methods=['POST'])
def remove_bookmark(id):
    l.remove_bookmark(request.user.id, id)
    return redirect(url_for('kitten', id=id))

@app.route('/kitten/<int:id>/mark_read/', methods=['POST'])
def mark_read(id):
    l.mark_read(request.user.id, id)
    return redirect(url_for('kitten', id=id))

"""
Author Feedback
"""
@app.route('/feedback/<key>')
def author_feedback(key):
    name, id = l.check_author_key(key)
    if not name:
        return render_template('bad_feedback_key.html')
    proposal = l.get_proposal(id)
    return render_template('author_feedback.html', name=name, 
                            proposal=proposal, messages=l.get_discussion(id))


@app.route('/feedback/<key>', methods=['POST'])
def author_post_feedback(key):
    name, id = l.check_author_key(key)
    if not name:
        return render_template('bad_feedback_key.html')
    message = request.values.get('message', '').strip()
    redir = redirect(url_for('author_feedback', key=key)) 
    if not message:
        flash('Empty message')
        return redir
    l.add_to_discussion(None, id, request.values.get('message'), name=name)
    flash('Your message has been saved!')
    return redir

"""
Default Action
"""
@app.route('/')
def pick():
    id = l.needs_votes(request.user.email, request.user.id)
    if not id:
        flash("You have voted on every proposal!")
        return redirect(url_for('show_votes'))
    return redirect(url_for('kitten', id=id))

if __name__ == '__main__':
    app.run(port=4000, debug=True)
