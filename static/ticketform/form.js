( function () {
	function refreshDescription() {
		var topicId = $( '#id_topic' ).val(),
			topic = window.topicsTable[ topicId ];
		if ( topicId === '' ) {
			$( '#topic_desc' ).hide();
			$( '#mediainfo-group' ).hide();
			$( '#expediture-group' ).hide();
			$( '#preexpediture-group' ).hide();
			$( '.field_car_travel' ).hide();
			return;
		}

		$( '#topic_desc' ).html( topic.form_description ).toggle( topic.form_description !== '' );
		$( '#mediainfo-group' ).toggle( topic.ticket_media );
		$( '#expediture-group' ).toggle( topic.ticket_expenses );
		$( '#preexpediture-group' ).toggle( topic.ticket_preexpenses );
		$( '.field_car_travel' ).toggle( topic.ticket_statutory_declaration );
	}

	function refreshSubtopicDescription() {
		var subtopicId = $( '#id_subtopic' ).val(),
			subtopic = window.subtopicsTable[ subtopicId ];
		if ( subtopicId === '' ) {
			$( '#subtopic_desc' ).hide();
			return;
		}

		$( '#subtopic_desc' ).html( subtopic.form_description ).toggle( subtopic.form_description !== '' );
	}

	$( document ).ready( function () {
		$( '#id_topic' ).change( refreshDescription );
		$( '#id_topic' ).change( refreshSubtopicDescription );
		$( '#id_subtopic' ).change( refreshSubtopicDescription );
		refreshDescription();
		refreshSubtopicDescription();
	} );
}() );
