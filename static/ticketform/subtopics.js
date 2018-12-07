( function () {
	function refreshSubtopics() {
		var topicId = $( '#id_topic' ).val(),
			topic = window.topicsTable[ topicId ],
			subtopicsHtml = '<option value selected>---------</option>',
			i, subtopic;
		if ( topicId === '' ) {
			$( '#id_subtopic' ).html( '<option value selected>---------</option>' );
			return;
		}
		for ( i = 0; i < topic.subtopic_set.length; i++ ) {
			subtopic = topic.subtopic_set[ i ];
			subtopicsHtml += '<option value="' + subtopic.id + '">' + subtopic.display_name + '</option>';
		}
		$( '#id_subtopic' ).html( subtopicsHtml );
		if ( $( '#id_subtopic' ).html().includes( window.originallyCheckedTag ) ) {
			$( '#id_subtopic' ).val( window.originallyCheckedTag );
		} else {
			$( '#id_subtopic' ).val( '' );
		}
	}

	$( document ).ready( function () {
		window.originallyCheckedTag = $( '#id_subtopic' ).val();
		$( '#id_topic' ).change( refreshSubtopics );
		refreshSubtopics();
	} );
}() );
