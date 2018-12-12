{
	document.addEventListener( 'DOMContentLoaded', async () => {
		const topicsJson = await fetch( '/api/tracker/topics/' ),
			subtopicsJson = await fetch( '/api/tracker/subtopics/' );

		window.topicsList = await topicsJson.json();
		window.subtopicsList = await subtopicsJson.json();
		window.dispatchEvent( new CustomEvent( 'TopicsDataLoaded' ) );

		const idTopic = document.querySelector( '#id_topic' ),
			idSubtopic = document.querySelector( '#id_subtopic' ),
			topicDesc = document.querySelector( '#topic_desc' ),
			subtopicDesc = document.querySelector( '#subtopic_desc' ),
			mediaInfoGroup = document.querySelector( '#mediainfo-group' ),
			expeditureGroup = document.querySelector( '#expediture-group' ),
			preexpeditureGroup = document.querySelector( '#preexpediture-group' ),
			fieldCarTravel = document.querySelector( '.field_car_travel' );

		function refreshDescription() {
			const topicId = idTopic.value,
				topic = getTopicById( topicId );
			if ( topicId === '' ) {
				[ topicDesc, mediaInfoGroup, expeditureGroup, preexpeditureGroup, fieldCarTravel ]
					.forEach( ( el ) => { el.hidden = true; } );
				return;
			}

			topicDesc.innerHTML = topic.form_description;
			topicDesc.hidden = topic.form_description === '';
			mediaInfoGroup.hidden = !!topic.ticket_media;
			expeditureGroup.hidden = !!topic.ticket_expenses;
			preexpeditureGroup.hidden = !!topic.ticket_preexpenses;
			fieldCarTravel.hidden = !!topic.ticket_statutory_declaration;
		}

		function refreshSubtopicDescription() {
			const subtopicId = idSubtopic.value,
				subtopic = getSubtopicById( subtopicId );
			if ( subtopicId === '' ) {
				subtopicDesc.hidden = true;
				return;
			}

			subtopicDesc.innerHTML = subtopic.form_description;
			subtopicDesc.hidden = subtopic.form_description !== '';
		}

		idTopic.addEventListener( 'change', refreshDescription );
		idTopic.addEventListener( 'change', refreshSubtopicDescription );
		idSubtopic.addEventListener( 'change', refreshSubtopicDescription );
		refreshDescription();
		refreshSubtopicDescription();
	} );
}
