# OpenOversight VA 

[OpenOversightVA.org](https://openoversightva.org/find) is Virginia's first and only police transparency database created by the public, for the public. We work to empower our communities with the facts about their local law enforcement. 
The data we maintain comes primarily from public records requests, open-source research, and crowdsourced contributions. 
Our database contains records on over 27,000 Virginia law enforcement officers, including some demographic information, salaries, work histories, incident histories, and digital galleries of photographs.

The website and concept were created as an independent fork of the original OpenOversight project based in Chicago thanks to open source code shared by the innovative team at Lucy Parsons Labs team.

This project is maintained entirely by a team of volunteers - collaboration, partnerships, and contributions are welcome. If you would like to contribute code or documentation, please email [admin@openoversightva.org](mailto:admin@openoversightva.org). You can also see this [contributing guide](/CONTRIB.md) and [code of conduct](/CODE_OF_CONDUCT.md). 

If you would like to volunteer in any way, please reach out to [alice@openoversightva.org](mailto:alice@openoversightva.org) or [admin@openoversightva.org](mailto:admin@openoversightva.org).

## Note to Law Enforcement

Please contact our legal representation with requests, questions, or concerns of a legal nature at [legal@openoversightva.org](mailto:legal@openoversightva.org).
Under Va. Code § 2.2-3705.1.(ii), public bodies are required to provide the names, job classifications, and salaries of their employees upon request by a Virginia resident. Freely disseminating this information in its entirety benefits the public interest, contributes to government transparency, and builds trust between public servants and the public itself. It is also protected by the First Amendment, with well-established legitimate precedent within state and federal case law. 

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
  * Demographic information - race, gender, etc.
  * Assignments - what bureau, precinct/division and/or beat are they assigned to? When has this changed?


For help acquiring this information from your local government, see our Wiki on [Police FOIA requests](https://github.com/openoversightva/openoversight/wiki/Police-FOIA-Requests-(Volunteer-Guide)).
* Clear images of officers*: Scrape through social media (as we have done) and/or solicit submissions. Encourage submissions with the badge number or name in frame such that it can be used to establish the face of the officer in the roster. After that point, new photos with a face matching the existing face in the database can be added to that officer's profile.
