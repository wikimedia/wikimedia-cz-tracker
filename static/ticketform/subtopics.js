( function () {
	document.addEventListener( 'DOMContentLoaded', function () {
		var idTopic = document.querySelector( '#id_topic' ),
			idSubtopic = document.querySelector( '#id_subtopic' );

		function refreshSubtopics() {
			var topicId = idTopic.value,
				topic = window.topicsTable[ topicId ],
				subtopicsHtml = '<option value selected>---------</option>',
				i, subtopic;
			if ( topicId === '' ) {
				idSubtopic.innerHTML = '<option value selected>---------</option>';
				return;
			}
			for ( i = 0; i < topic.subtopic_set.length; i++ ) {
				subtopic = topic.subtopic_set[ i ];
				subtopicsHtml += '<option value="' + subtopic.id + '">' + subtopic.display_name + '</option>';
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
}() );
