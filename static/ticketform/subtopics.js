{
	window.addEventListener( 'TopicsDataLoaded', () => {
		const idTopic = document.querySelector( '#id_topic' ),
			idSubtopic = document.querySelector( '#id_subtopic' );

		function refreshSubtopics() {
			const topicId = idTopic.value,
				topic = getTopicById( topicId );
			let i, subtopic,
				subtopicsHtml = '<option value selected>---------</option>';
			if ( topicId === '' ) {
				idSubtopic.innerHTML = '<option value selected>---------</option>';
				return;
			}
			for ( i = 0; i < topic.subtopics.length; i++ ) {
				subtopic = topic.subtopics[ i ];
				subtopicsHtml += `<option value="${subtopic.id}">${subtopic.display_name}</option>`;
			}
			idSubtopic.innerHTML = subtopicsHtml;
			if ( idSubtopic.innerHTML.includes( window.originallyCheckedTag ) ) {
				idSubtopic.value = window.originallyCheckedTag;
			} else {
				idSubtopic.value = '';
			}
		}

		window.originallyCheckedTag = idSubtopic.value;
		idTopic.addEventListener( 'change', refreshSubtopics );
		refreshSubtopics();
	} );
}
