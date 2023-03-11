# OpenOversight Virginia 

OpenOversight Virginia is a fork of OpenOversight, a Lucy Parsons Labs project to improve law enforcement accountability through public and crowdsourced data. We maintain a database of officer demographic information and provide digital galleries of photographs. This is done to help people identify law enforcement officers for filing complaints and in order for the public to see work-related information about law enforcement officers that interact with the public.

This project is maintained entirely by a team of volunteers - collaboration, partnerships, and contributions are welcome. If you would like to contribute code or documentation, please see our [contributing guide](/CONTRIB.md) and [code of conduct](/CODE_OF_CONDUCT.md). 

If you would like to volunteer in any way, please reach out to [openoversightva@riseup.net]

## Note to Law Enforcement

Please contact our legal representation with requests, questions, or concerns of a legal nature by emailing [legal@lucyparsonslabs.com](mailto:legal@lucyparsonslabs.com).

## Issues

Please use [our issue tracker](https://github.com/openoversightva/openoversight/issues/new) to submit issues or suggestions.

## Developer Quickstart

Make sure you have Docker installed and then:

```
git clone https://github.com/openoversightva/openoversight.git
cd OpenOversight
make dev
```

And open `http://localhost:3000` in your favorite browser!

If you need to log in, use the auto-generated test account
credentials:

```
Email: test@example.org
Password: testtest
```

Please see [CONTRIB.md](/CONTRIB.md) for the full developer setup instructions.

## Documentation Quickstart

```
pip install -r dev-requirements.txt
make docs
```

## Deployment

Please see the [DEPLOY.md](/DEPLOY.md) file for deployment instructions.

## What data do I need to set up OpenOversight in my city?

* *Officer roster/assignment/demographic information*: You can often acquire a huge amount of information through FOIA:
  * Roster of all police officers (names, badge numbers)
  * Badge/star number history (if badge/star numbers change upon promotion)
  * Demographic information - race, gender, etc.
  * Assignments - what bureau, precinct/division and/or beat are they assigned to? When has this changed?
*Clear images of officers*: Scrape through social media (as we have done) and/or solicit submissions. Encourage submissions with the badge number or name in frame such that it can be used to establish the face of the officer in the roster. After that point, new photos with a face matching the existing face in the database can be added to that officer's profile.
